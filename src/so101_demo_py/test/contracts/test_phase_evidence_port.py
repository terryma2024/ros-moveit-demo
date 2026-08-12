from dataclasses import dataclass, field

from so101_demo.backends.mujoco.phase_evidence import MujocoPhaseEvidenceAdapter
from so101_demo.ports.phase_evidence import PhaseEvidencePort


@dataclass
class FakeTraceObserver:
    calls: list[tuple[str, object]] = field(default_factory=list)

    def mark_goal_dispatched(self, *, waypoint: int):
        self.calls.append(("goal", waypoint))
        return type("Boundary", (), {"physics_step": 10})()

    def mark_waypoint_complete(self, *, waypoint: int):
        self.calls.append(("waypoint", waypoint))
        return type("Boundary", (), {"physics_step": 20})()

    def mark_phase_complete(self, *, waypoint: int):
        self.calls.append(("phase", waypoint))
        return type("Boundary", (), {"physics_step": 30})()

    def build_run(self, *, physics_timestep_s: float, physical_transport_outcome: str):
        self.calls.append(("finish", physical_transport_outcome))
        return type("Run", (), {"evidence_loss": False})()


def test_phase_trace_is_observation_only_and_identity_bound() -> None:
    """Catch instrumentation that mutates execution or loses trace identity."""

    observer = FakeTraceObserver()
    adapter = MujocoPhaseEvidenceAdapter(
        lambda phase: observer,
        simulation_session_id="session-1",
        reset_epoch=3,
        physics_timestep_s=0.002,
    )
    receipt = adapter.begin_trace("transport")
    boundary = adapter.mark_boundary(receipt.trace_id, "waypoint_start:2")
    trace = adapter.finish_trace(receipt.trace_id)
    assert boundary.physics_step == 10
    assert trace.lossless
    assert trace.session_id == "session-1"
    assert observer.calls == [("goal", 2), ("finish", "SUCCEEDED")]


def test_phase_evidence_port_exposes_optional_trace_methods() -> None:
    assert set(PhaseEvidencePort.__protocol_attrs__) >= {
        "begin_trace",
        "mark_boundary",
        "finish_trace",
    }
