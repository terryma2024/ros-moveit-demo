"""Task 5 (approved measurement protocol v2): the production MuJoCo measurement driver.

The driver acquires raw evidence for three anchors in order, each in its own FULL_RESTART identity, and seals only
a CLOSED or INVALID batch. It emits raw records - never a verdict, never a label - and a failure in any anchor stops
the later anchors, cleans up exactly once for the current generation, and seals INVALID with no report. ROS,
detector, controller and MuJoCo are faked here; no second real stack is launched in unit tests.
"""

import json
from pathlib import Path

import pytest

FORBIDDEN_TOKENS = ("PASS", "FAIL", "qualified", "visible", "target_in_view", "contact_ok", "_ok")
ANCHOR_ORDER = ["default", "left", "forward"]
INDEX_ROW_KEYS = {"source_stamp", "receive_monotonic_s", "session_id", "reset_epoch", "attempt_id",
                  "physics_step", "payload_path", "payload_sha256", "encoding", "shape"}


class FakeStack:
    """Records launch/close order and can be told to fail on a given anchor."""

    def run_search(self, anchor, request):
        return {"iterations": [{"yaw_rad": 0.0}], "terminated": "COARSE_STEP_LIMIT"}

    def __init__(self, *, fail_on=None):
        self.launched, self.closed, self.cleanups = [], [], []
        self.fail_on = fail_on

    def probe(self, anchor, command):
        return {"contacts": []}

    def camera_info(self, anchor):
        return {"width": 640, "height": 480, "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0]}

    def tf(self, anchor):
        return {"head": {"translation_m": [0.0, 0.0, 1.0], "rpy_rad": [0.0, 0.0, 0.0]}, "wrist": {"translation_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}

    def readback(self, anchor):
        return {"session_id": f"session-{anchor}", "reset_epoch": 1, "attempt_id": f"attempt-{anchor}"}

    def launch(self, anchor):
        self.launched.append(anchor)
        if anchor == self.fail_on:
            raise RuntimeError("STACK_LAUNCH_FAILED")

    def close(self, anchor):
        self.closed.append(anchor)

    def cleanup(self, anchor, generation):
        self.cleanups.append((anchor, generation))
        return {"cleaned": True, "generation": generation}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        self.now += 0.1
        return self.now


def _identity():
    """The schema's ten-member measurement identity, as the CLI holds it and passes it to the driver."""

    return {"source_commit": "0" * 40,
            **{name: "a" * 64 for name in (
                "config_sha256", "source_provenance_sha256", "runtime_config_sha256", "anchors_sha256",
                "contact_policy_fingerprint", "act_profile_sha256", "measurement_contract_sha256",
                "phase_camera_matrix_sha256", "driver_source_sha256")}}


def _driver(stack):
    from so101_demo.act.task8_measurement_driver import Task8MujocoMeasurementDriver

    return Task8MujocoMeasurementDriver(stack=stack, clock=FakeClock(), detector=lambda frame: {"bbox": [10, 10, 20, 20]},
                                        controller=lambda command: {"accepted": True},
                                        # the phase camera reports raw observation rows; a verdict here is refused by
                                        # the raw layer's own token rule, which is what the driver enforces
                                        phase_camera=lambda phase, index: {"phase": phase, "frame_index": index,
                                                                           "row_count": 0}, identity=_identity())


def _context():
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    return CalibrationMeasurementContext(runtime_descriptor={"schema_version": 1, "head_search": {"schema_version": 1, "detector": {"requested_device": "cuda", "allow_cpu_fallback": False}, "camera": {}, "motion": {}}},
        generation="g1", contract_sha256="a" * 64, measurement_plan_sha256="b" * 64,
        safe_interval_rad=[-1.0, 1.0], candidate_sha256="c" * 64, policy_sha256="d" * 64,
        driver_source_sha256="e" * 64, controller_generation="ctrl-1", broker_generation="g1",
        evidence_root="/data/work/so101-evidence/act-data/run",
        resource_binding={"bound_at_entry": True, "cpu_cores": 8, "gpu_device": 0})


def test_a_valid_run_executes_the_anchors_in_order_with_separate_identities(tmp_path):
    stack = FakeStack()
    path = _driver(stack).run(_context(), tmp_path)
    assert stack.launched == ANCHOR_ORDER
    assert stack.closed == ANCHOR_ORDER
    batch = json.loads(path.read_bytes())
    assert batch["status"] == "CLOSED" and batch["kind"] == "task8_calibration_batch"
    identities = {tuple(sorted(entry["identity"].items())) for entry in json.loads((path.parent / "index.json").read_bytes())["anchors"]}
    assert len(identities) == 3, "every anchor needs its own FULL_RESTART session/reset/attempt"


def test_a_failing_anchor_stops_later_anchors_cleans_up_once_and_seals_invalid(tmp_path):
    stack = FakeStack(fail_on="left")
    path = _driver(stack).run(_context(), tmp_path)
    assert stack.launched == ["default", "left"]
    assert stack.closed == ["default"]
    assert len(stack.cleanups) == 1 and stack.cleanups[0][1] == "g1"
    batch = json.loads(path.read_bytes())
    assert batch["status"] == "INVALID"
    assert "report" not in batch and batch["error_code"] == "STACK_LAUNCH_FAILED"


def test_no_driver_output_carries_a_verdict_or_a_label(tmp_path):
    path = _driver(FakeStack()).run(_context(), tmp_path)
    root = path.parent
    for document in sorted(root.rglob("*.json")):
        text = document.read_text()
        for token in FORBIDDEN_TOKENS:
            assert token not in text, f"{document.name} carries {token}"


def test_every_index_row_carries_the_required_provenance_fields(tmp_path):
    path = _driver(FakeStack()).run(_context(), tmp_path)
    batch = json.loads(path.read_bytes())
    rows = json.loads((path.parent / "index.json").read_bytes())["files"]   # the records have an indexed home
    assert rows, "the driver must register its raw records"
    # the provenance fields belong to the raw-record rows; the descriptor and index.json rows are artefacts of the
    # seal's closure rather than of an anchor capture, so the assertion is scoped to the anchors (CP-1246)
    for row in [r for r in rows if str(r["payload_path"]).startswith("anchors/")]:
        assert INDEX_ROW_KEYS <= set(row), sorted(INDEX_ROW_KEYS - set(row))
        payload = path.parent / row["payload_path"]
        assert payload.is_file(), row["payload_path"]
        assert len(row["payload_sha256"]) == 64 and row["encoding"] and row["shape"]


def test_only_a_closed_or_invalid_batch_is_ever_returned(tmp_path):
    for stack, expected in ((FakeStack(), "CLOSED"), (FakeStack(fail_on="default"), "INVALID")):
        path = _driver(stack).run(_context(), tmp_path / expected)
        assert json.loads(path.read_bytes())["status"] == expected
        assert path.name == "batch.json"


def test_the_cli_defaults_to_the_production_driver():
    source = (Path(__file__).resolve().parents[1] / "src/cli/act_measure_task8_calibration.py").read_text()
    assert "Task8MujocoMeasurementDriver" in source
    assert "--driver" in source, "injection must be an explicit, test-only option"


def test_the_production_factory_fails_closed_while_stack_wiring_is_absent():
    from so101_demo.act.task8_measurement_driver import production_driver

    with pytest.raises(ValueError, match="PRODUCTION_DRIVER_WIRING_PENDING"):
        production_driver()


def test_each_anchor_runs_the_private_phase_replay_through_the_phase_camera(tmp_path):
    """Boundary II: the phase camera is a real dependency, so every anchor must actually replay the nine phases.

    Today the driver stores ``phase_camera`` and never calls it, so a run can seal CLOSED while no phase coverage was
    ever evaluated - the coverage the measurement contract's phase matrix depends on.
    """

    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext
    from so101_demo.act.task8_measurement_driver import ANCHORS, Task8MujocoMeasurementDriver

    phases: list[tuple[str, str]] = []

    class Stack:
        def run_search(self, anchor, request):
            return {"iterations": [{"yaw_rad": 0.0}], "terminated": "COARSE_STEP_LIMIT"}

        def __init__(self):
            self.launched, self.closed, self.cleaned = [], [], []

        def probe(self, anchor, command):
            return {"contacts": []}

        def camera_info(self, anchor):
            return {"width": 640, "height": 480, "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0]}

        def tf(self, anchor):
            return {"head": {"translation_m": [0.0, 0.0, 1.0], "rpy_rad": [0.0, 0.0, 0.0]}, "wrist": {"translation_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}

        def readback(self, anchor):
            return {"session_id": f"session-{anchor}", "reset_epoch": 1, "attempt_id": f"attempt-{anchor}"}

        def launch(self, anchor):
            self.launched.append(anchor)

        def close(self, anchor):
            self.closed.append(anchor)

        def cleanup(self, anchor, generation):
            self.cleaned.append((anchor, generation))

    class Clock:
        """The driver reads ``clock.monotonic()``, so the fake exposes that surface rather than being a bare callable."""

        def __init__(self):
            self.now = 0.0

        def monotonic(self):
            self.now += 0.002
            return self.now

    stack = Stack()
    driver = Task8MujocoMeasurementDriver(
        stack=stack, clock=Clock(), detector=lambda request: {"anchor": request["anchor"]},
        controller=lambda request: {"ack": True},
        phase_camera=lambda phase, sample: phases.append((phase, sample)), identity=_identity())
    # the real context, so only external I/O is faked; its digests are 64-hex and the binding happens at the entry
    context = CalibrationMeasurementContext(runtime_descriptor={"schema_version": 1, "head_search": {"schema_version": 1, "detector": {"requested_device": "cuda", "allow_cpu_fallback": False}, "camera": {}, "motion": {}}},
        generation="generation-1", contract_sha256="a" * 64, measurement_plan_sha256="b" * 64,
        safe_interval_rad=(-0.1, 0.1), candidate_sha256="c" * 64, policy_sha256="d" * 64,
        driver_source_sha256="e" * 64, controller_generation="controller-1",
        broker_generation="broker-1", evidence_root=str(tmp_path),
        resource_binding={"bound_at_entry": True, "cpu_cores": 8, "gpu_device": "0"})
    sealed = driver.run(context, tmp_path / "batch")

    assert Path(sealed).is_file()
    assert stack.launched == list(ANCHORS), "every anchor is launched"
    assert stack.closed == list(ANCHORS), "every anchor is closed"
    assert stack.cleaned == [(ANCHORS[-1], "generation-1")]
    assert len(phases) == len(ANCHORS) * 9, f"nine phases per anchor, saw {len(phases)}"


def _measurement_context(tmp_path, generation="generation-1"):
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    return CalibrationMeasurementContext(runtime_descriptor={"schema_version": 1, "head_search": {"schema_version": 1, "detector": {"requested_device": "cuda", "allow_cpu_fallback": False}, "camera": {}, "motion": {}}},
        generation=generation, contract_sha256="a" * 64, measurement_plan_sha256="b" * 64,
        safe_interval_rad=(-0.1, 0.1), candidate_sha256="c" * 64, policy_sha256="d" * 64,
        driver_source_sha256="e" * 64, controller_generation="controller-1",
        broker_generation="broker-1", evidence_root=str(tmp_path),
        resource_binding={"bound_at_entry": True, "cpu_cores": 8, "gpu_device": "0"})


def test_a_failed_anchor_keeps_a_cleanup_receipt_in_the_sealed_batch(tmp_path):
    """Boundary II: a failure seals INVALID, cleans up once for this generation, and keeps the receipt as evidence."""

    from so101_demo.act.task8_measurement_driver import ANCHORS, Task8MujocoMeasurementDriver

    cleaned = []

    class Stack:
        def run_search(self, anchor, request):
            return {"iterations": [{"yaw_rad": 0.0}], "terminated": "COARSE_STEP_LIMIT"}

        def camera_info(self, anchor):
            return {"width": 640, "height": 480, "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0]}

        def tf(self, anchor):
            return {"head": {"translation_m": [0.0, 0.0, 1.0], "rpy_rad": [0.0, 0.0, 0.0]}, "wrist": {"translation_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}

        def readback(self, anchor):
            return {"session_id": f"session-{anchor}", "reset_epoch": 1, "attempt_id": f"attempt-{anchor}"}

        def probe(self, anchor, command):
            return {"contacts": []}

        def launch(self, anchor):
            pass

        def close(self, anchor):
            pass

        def cleanup(self, anchor, generation):
            cleaned.append((anchor, generation))

    class Clock:
        def monotonic(self):
            return 0.0

    def detector(request):
        raise RuntimeError("DETECTOR_UNAVAILABLE")

    driver = Task8MujocoMeasurementDriver(
        stack=Stack(), clock=Clock(), detector=detector, controller=lambda command: {"accepted": True},
        phase_camera=lambda phase, index: {"phase": phase, "frame_index": index, "row_count": 0}, identity=_identity())
    sealed = driver.run(_measurement_context(tmp_path), tmp_path / "batch")
    document = json.loads(Path(sealed).read_text())

    assert document["status"] == "INVALID"
    assert cleaned == [(ANCHORS[0], "generation-1")], "cleanup runs once, for this case's own generation"
    text = json.dumps(document)
    assert "cleanup" in text, "the sealed batch keeps the cleanup receipt"
    assert ANCHORS[0] in text and ANCHORS[1] not in text, "no later anchor is attempted after a failure"


def test_a_cleanup_failure_contaminates_the_batch_and_stops_the_run(tmp_path):
    """A cleanup that fails must be recorded as contamination rather than escaping as an unattributed exception."""

    from so101_demo.act.task8_measurement_driver import Task8MujocoMeasurementDriver

    class Stack:
        def run_search(self, anchor, request):
            return {"iterations": [{"yaw_rad": 0.0}], "terminated": "COARSE_STEP_LIMIT"}

        def camera_info(self, anchor):
            return {"width": 640, "height": 480, "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0]}

        def tf(self, anchor):
            return {"head": {"translation_m": [0.0, 0.0, 1.0], "rpy_rad": [0.0, 0.0, 0.0]}, "wrist": {"translation_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}

        def readback(self, anchor):
            return {"session_id": f"session-{anchor}", "reset_epoch": 1, "attempt_id": f"attempt-{anchor}"}

        def probe(self, anchor, command):
            return {"contacts": []}

        def launch(self, anchor):
            pass

        def close(self, anchor):
            pass

        def cleanup(self, anchor, generation):
            raise RuntimeError("CLEANUP_REFUSED")

    class Clock:
        def monotonic(self):
            return 0.0

    driver = Task8MujocoMeasurementDriver(
        stack=Stack(), clock=Clock(), detector=lambda request: {"bbox": [0, 0, 1, 1]},
        controller=lambda command: {"accepted": True},
        phase_camera=lambda phase, index: {"phase": phase, "frame_index": index, "row_count": 0}, identity=_identity())
    sealed = driver.run(_measurement_context(tmp_path), tmp_path / "batch")
    document = json.loads(Path(sealed).read_text())
    assert document["status"] == "INVALID"
    assert "contaminat" in json.dumps(document).lower(), "a failed cleanup is recorded as contamination"


def test_rows_carry_the_stack_readback_rather_than_a_synthesized_identity(tmp_path):
    """Boundary II: session, reset epoch and attempt come from the stack's readback, not from the anchor ordinal."""

    from so101_demo.act.task8_measurement_driver import Task8MujocoMeasurementDriver

    class Stack:
        def run_search(self, anchor, request):
            return {"iterations": [{"yaw_rad": 0.0}], "terminated": "COARSE_STEP_LIMIT"}

        def probe(self, anchor, command):
            return {"contacts": []}

        def camera_info(self, anchor):
            return {"width": 640, "height": 480, "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0]}

        def tf(self, anchor):
            return {"head": {"translation_m": [0.0, 0.0, 1.0], "rpy_rad": [0.0, 0.0, 0.0]}, "wrist": {"translation_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}

        def launch(self, anchor):
            pass

        def readback(self, anchor):
            return {"session_id": f"session-{anchor}", "reset_epoch": 7, "attempt_id": f"attempt-{anchor}"}

        def close(self, anchor):
            pass

        def cleanup(self, anchor, generation):
            return {"cleaned": anchor}

    class Clock:
        def monotonic(self):
            return 0.0

    driver = Task8MujocoMeasurementDriver(
        stack=Stack(), clock=Clock(), detector=lambda request: {"bbox": [0, 0, 1, 1]},
        controller=lambda command: {"accepted": True},
        phase_camera=lambda phase, index: {"phase": phase, "frame_index": index, "row_count": 0}, identity=_identity())
    batch = tmp_path / "batch"
    driver.run(_measurement_context(tmp_path), batch)
    row = json.loads((batch / "anchors/default/geometry-00.json").read_text())
    assert row["session_id"] == "session-default"
    assert row["reset_epoch"] == 7
    assert row["attempt_id"] == "attempt-default"


def test_a_stack_without_readback_is_refused_by_name(tmp_path):
    from so101_demo.act.task8_measurement_driver import Task8MujocoMeasurementDriver

    class Stack:
        def run_search(self, anchor, request):
            return {"iterations": [{"yaw_rad": 0.0}], "terminated": "COARSE_STEP_LIMIT"}

        def probe(self, anchor, command):
            return {"contacts": []}

        def camera_info(self, anchor):
            return {"width": 640, "height": 480, "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0]}

        def tf(self, anchor):
            return {"head": {"translation_m": [0.0, 0.0, 1.0], "rpy_rad": [0.0, 0.0, 0.0]}, "wrist": {"translation_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}

        def launch(self, anchor):
            pass

        def close(self, anchor):
            pass

        def cleanup(self, anchor, generation):
            return {"cleaned": anchor}

    class Clock:
        def monotonic(self):
            return 0.0

    driver = Task8MujocoMeasurementDriver(
        stack=Stack(), clock=Clock(), detector=lambda request: {"bbox": [0, 0, 1, 1]},
        controller=lambda command: {"accepted": True},
        phase_camera=lambda phase, index: {"phase": phase, "frame_index": index, "row_count": 0}, identity=_identity())
    sealed = driver.run(_measurement_context(tmp_path), tmp_path / "batch")
    document = json.loads(Path(sealed).read_text())
    assert document["status"] == "INVALID"
    assert "READBACK" in json.dumps(document), "a stack that cannot report its identity fails closed by name"


def test_every_anchor_is_an_independent_full_restart(tmp_path):
    """Boundary II: default, left and forward are three separate FULL_RESTART lifecycles, never overlapping."""

    from so101_demo.act.task8_measurement_driver import ANCHORS, Task8MujocoMeasurementDriver

    events: list[tuple[str, str]] = []

    class Stack:
        def run_search(self, anchor, request):
            return {"iterations": [{"yaw_rad": 0.0}], "terminated": "COARSE_STEP_LIMIT"}

        def probe(self, anchor, command):
            return {"contacts": []}

        def camera_info(self, anchor):
            return {"width": 640, "height": 480, "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0]}

        def tf(self, anchor):
            return {"head": {"translation_m": [0.0, 0.0, 1.0], "rpy_rad": [0.0, 0.0, 0.0]}, "wrist": {"translation_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}

        def readback(self, anchor):
            return {"session_id": f"session-{anchor}", "reset_epoch": 1, "attempt_id": f"attempt-{anchor}"}

        def launch(self, anchor):
            events.append(("launch", anchor))

        def close(self, anchor):
            events.append(("close", anchor))

        def cleanup(self, anchor, generation):
            events.append(("cleanup", anchor))
            return {"cleaned": anchor}

    class Clock:
        def monotonic(self):
            return 0.0

    driver = Task8MujocoMeasurementDriver(
        stack=Stack(), clock=Clock(), detector=lambda request: {"bbox": [0, 0, 1, 1]},
        controller=lambda command: {"accepted": True},
        phase_camera=lambda phase, index: {"phase": phase, "frame_index": index, "row_count": 0}, identity=_identity())
    batch = tmp_path / "batch"
    sealed = driver.run(_measurement_context(tmp_path), batch)
    document = json.loads(Path(sealed).read_text())
    assert document["status"] == "CLOSED"

    lifecycle = [entry for entry in events if entry[0] in ("launch", "close")]
    assert lifecycle == [(action, anchor) for anchor in ANCHORS for action in ("launch", "close")], lifecycle
    row = json.loads((batch / "anchors/default/geometry-00.json").read_text())
    assert row["lifecycle"] == "FULL_RESTART", "every row names the lifecycle it was measured under"


def _probe_driver(stack, clock=None):
    from so101_demo.act.task8_measurement_driver import Task8MujocoMeasurementDriver

    class Clock:
        def monotonic(self):
            return 0.0

    return Task8MujocoMeasurementDriver(
        stack=stack, clock=clock or Clock(), detector=lambda request: {"bbox": [0, 0, 1, 1]},
        controller=lambda command: {"accepted": True},
        phase_camera=lambda phase, index: {"phase": phase, "frame_index": index, "row_count": 0}, identity=_identity())


class _ProbeStack:
    """A stack that reports contacts for the probe; ``hits`` decides whether the probe touched anything."""

    def run_search(self, anchor, request):
        return {"iterations": [{"yaw_rad": 0.0}], "terminated": "COARSE_STEP_LIMIT"}

    def __init__(self, hits):
        self.hits = hits
        self.probes = []

    def camera_info(self, anchor):
        return {"width": 640, "height": 480, "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0]}

    def tf(self, anchor):
        return {"head": {"translation_m": [0.0, 0.0, 1.0], "rpy_rad": [0.0, 0.0, 0.0]}, "wrist": {"translation_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}

    def readback(self, anchor):
        return {"session_id": f"session-{anchor}", "reset_epoch": 1, "attempt_id": f"attempt-{anchor}"}

    def launch(self, anchor):
        pass

    def close(self, anchor):
        pass

    def cleanup(self, anchor, generation):
        return {"cleaned": anchor}

    def probe(self, anchor, command):
        self.probes.append((anchor, command))
        return {"contacts": [{"geom1": "arm_link", "geom2": "cup"}] if self.hits else []}


def test_the_fixed_arm_probe_is_recorded_and_must_not_contact_anything(tmp_path):
    """Boundary II: a fixed non-contact arm probe runs per anchor and a touch fails that anchor by name."""

    stack = _ProbeStack(hits=False)
    batch = tmp_path / "batch"
    sealed = _probe_driver(stack).run(_measurement_context(tmp_path), batch)
    document = json.loads(Path(sealed).read_text())
    assert document["status"] == "CLOSED"
    assert len(stack.probes) == 3, "one probe per anchor"
    probe_row = json.loads((batch / "anchors/default/probe.json").read_text())
    assert probe_row["contact_count"] == 0 and probe_row["lifecycle"] == "FULL_RESTART"


def test_a_probe_that_touches_anything_fails_the_anchor_by_name(tmp_path):
    stack = _ProbeStack(hits=True)
    sealed = _probe_driver(stack).run(_measurement_context(tmp_path), tmp_path / "batch")
    document = json.loads(Path(sealed).read_text())
    assert document["status"] == "INVALID"
    assert "MEASUREMENT_PROBE_CONTACT" in json.dumps(document)


class _CameraStack:
    """A stack that reports the camera intrinsics and the head/wrist transforms it actually used."""

    def run_search(self, anchor, request):
        return {"iterations": [{"yaw_rad": 0.0}], "terminated": "COARSE_STEP_LIMIT"}

    def __init__(self, camera=True):
        self.camera = camera

    def readback(self, anchor):
        return {"session_id": f"session-{anchor}", "reset_epoch": 1, "attempt_id": f"attempt-{anchor}"}

    def launch(self, anchor):
        pass

    def close(self, anchor):
        pass

    def cleanup(self, anchor, generation):
        return {"cleaned": anchor}

    def probe(self, anchor, command):
        return {"contacts": []}

    def camera_info(self, anchor):
        if not self.camera:
            raise AttributeError("no camera surface")
        return {"width": 640, "height": 480,
                "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0]}

    def tf(self, anchor):
        if not self.camera:
            raise AttributeError("no tf surface")
        return {"head": {"translation_m": [0.0, 0.0, 1.0], "rpy_rad": [0.0, 0.0, 0.0]},
                "wrist": {"translation_m": [0.0, 0.0, 0.5], "rpy_rad": [0.0, 0.0, 0.0]}}


def test_each_anchor_records_the_camera_info_and_transforms_it_used(tmp_path):
    """Boundary II: the raw batch carries real CameraInfo and TF rows, not just a claimed intrinsics field."""

    batch = tmp_path / "batch"
    sealed = _probe_driver(_CameraStack()).run(_measurement_context(tmp_path), batch)
    assert json.loads(Path(sealed).read_text())["status"] == "CLOSED"
    info = json.loads((batch / "anchors/default/camera-info.json").read_text())
    tf_row = json.loads((batch / "anchors/default/tf.json").read_text())
    assert info["width"] == 640 and len(info["k"]) == 9
    assert set(tf_row["head"]) == {"translation_m", "rpy_rad"} and "wrist" in tf_row
    assert info["lifecycle"] == tf_row["lifecycle"] == "FULL_RESTART"


def test_a_stack_that_cannot_report_camera_evidence_fails_closed_by_name(tmp_path):
    sealed = _probe_driver(_CameraStack(camera=False)).run(_measurement_context(tmp_path), tmp_path / "batch")
    document = json.loads(Path(sealed).read_text())
    assert document["status"] == "INVALID"
    assert "MEASUREMENT_CAMERA_REQUIRED" in json.dumps(document)


class _SearchStack(_CameraStack):
    """A stack that also exposes the live search path the measurement is supposed to exercise."""

    def __init__(self, search=True):
        super().__init__()
        self.search = search
        self.requests = []

    def run_search(self, anchor, request):
        if not self.search:
            raise AttributeError("no search surface")
        self.requests.append((anchor, dict(request)))
        return {"iterations": [{"yaw_rad": 0.0}, {"yaw_rad": 0.05}], "terminated": "COARSE_STEP_LIMIT"}


def test_each_anchor_runs_the_live_search_and_keeps_its_raw_iterations(tmp_path):
    stack = _SearchStack()
    batch = tmp_path / "batch"
    sealed = _probe_driver(stack).run(_measurement_context(tmp_path), batch)
    assert json.loads(Path(sealed).read_text())["status"] == "CLOSED"
    assert [anchor for anchor, _ in stack.requests] == ["default", "left", "forward"]
    row = json.loads((batch / "anchors/default/search.json").read_text())
    assert len(row["iterations"]) == 2 and row["terminated"] == "COARSE_STEP_LIMIT"
    assert row["lifecycle"] == "FULL_RESTART"


def test_a_stack_that_cannot_search_fails_closed_by_name(tmp_path):
    sealed = _probe_driver(_SearchStack(search=False)).run(_measurement_context(tmp_path), tmp_path / "batch")
    assert "MEASUREMENT_SEARCH_REQUIRED" in json.dumps(json.loads(Path(sealed).read_text()))


def _runtime_descriptor():
    return {"schema_version": 1, "head_search": {
        "schema_version": 1,
        "detector": {"backend": "yolo_seg", "weights_path": "/weights/best.pt", "weights_sha256": "a" * 64,
                     "model_id": "plastic-cup", "image_size_px": 640, "requested_device": "cuda",
                     "allow_cpu_fallback": False, "torch_threads": 4, "torch_interop_threads": 2,
                     "torch_version": "2.0", "ultralytics_version": "8.0"},
        "camera": {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
                   "width_px": 640, "height_px": 480},
        "motion": {"goal_tolerance_rad": 0.02, "settle_velocity_rad_s": 0.01, "neck_goal_duration_s": 0.5}}}


def test_the_driver_registers_the_runtime_descriptor_with_the_batch_it_seals(tmp_path):
    """Section 4.2/3.1: the descriptor the measurement ran under travels with the raw batch, so a later report can be
    bound to it - and the closed index covers it like every other file."""

    import json as _json

    context = _measurement_context(tmp_path, generation="generation-descriptor")
    context.runtime_descriptor = _runtime_descriptor()
    root = tmp_path / "batch"
    _driver(FakeStack()).run(context, root)

    recorded = []
    for path in sorted(root.rglob("*.json")):
        try:
            document = _json.loads(path.read_bytes())
        except (UnicodeDecodeError, _json.JSONDecodeError):
            continue
        if isinstance(document, dict) and isinstance(document.get("head_search"), dict):
            recorded.append((path, document["head_search"]))
    assert recorded, "the sealed batch records the descriptor it was measured under"
    assert any(descriptor == context.runtime_descriptor["head_search"] for _, descriptor in recorded)


def test_the_drivers_own_batch_passes_the_schema_validator_and_carries_the_descriptor(tmp_path):
    """Astra item 3: the driver's real output must satisfy the schema, with the descriptor in the hash index.

    This drives the driver itself - no hand-built document, no rglob over JSON, no second seal - and then asks the
    schema's own validator to close the batch. Today the driver writes a stray ``index`` key and no ``batch_sha256``,
    so the validator refuses it; that is the RED.
    """

    from so101_demo.act.task8_measurement_schema import validate_closed_batch

    context = _measurement_context(tmp_path)
    driver = _driver(FakeStack())
    sealed = Path(driver.run(context, tmp_path / "batch"))

    index = validate_closed_batch(sealed.parent)
    assert "runtime-descriptor.json" in set(index.files), "the descriptor must be in the sealed hash index"
