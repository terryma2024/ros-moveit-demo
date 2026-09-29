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

    def __init__(self, *, fail_on=None):
        self.launched, self.closed, self.cleanups = [], [], []
        self.fail_on = fail_on

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


def _driver(stack):
    from so101_demo.act.task8_measurement_driver import Task8MujocoMeasurementDriver

    return Task8MujocoMeasurementDriver(stack=stack, clock=FakeClock(), detector=lambda frame: {"bbox": [10, 10, 20, 20]},
                                        controller=lambda command: {"accepted": True},
                                        # the phase camera reports raw observation rows; a verdict here is refused by
                                        # the raw layer's own token rule, which is what the driver enforces
                                        phase_camera=lambda phase, index: {"phase": phase, "frame_index": index,
                                                                           "row_count": 0})


def _context():
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    return CalibrationMeasurementContext(
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
    identities = {tuple(sorted(entry["identity"].items())) for entry in batch["anchors"]}
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
    rows = batch["index"]
    assert rows, "the driver must register its raw records"
    for row in rows:
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
        def __init__(self):
            self.launched, self.closed, self.cleaned = [], [], []

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
        phase_camera=lambda phase, sample: phases.append((phase, sample)))
    # the real context, so only external I/O is faked; its digests are 64-hex and the binding happens at the entry
    context = CalibrationMeasurementContext(
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
