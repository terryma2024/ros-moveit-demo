import json
from pathlib import Path
from threading import Event, Thread

import pytest
from so101_demo.application.dynamic_transport_evidence import (
    AtomicTransportEvidenceStore,
    EvidenceInvalid,
    PhysicsStepChunk,
    PhysicsStepSample,
)
from so101_demo.backends.mujoco.transport_observer import (
    DynamicTransportEvidenceObserver,
)


def _chunk(sequence: int = 1, physics_step: int = 1) -> PhysicsStepChunk:
    sample = PhysicsStepSample(
        simulation_session_id="session",
        reset_epoch=1,
        physics_step=physics_step,
        simulation_time_s=physics_step * 0.002,
        object_pose_world_xyz_xyzw=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        object_twist_world_linear_angular=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        maximum_normal_force_n=0.0,
        left_fingertip_total_normal_force_n=0.0,
        right_fingertip_total_normal_force_n=0.0,
        fingertip_max_single_contact_force_n=0.0,
        global_max_single_contact_force_n=0.0,
        left_fingertip_compression_m=0.0,
        right_fingertip_compression_m=0.0,
        net_contact_force_world_n=(0.0, 0.0, 0.0),
        truncated=False,
        left_fingertip_contacts=(),
        right_fingertip_contacts=(),
        other_object_contacts=(),
    )
    return PhysicsStepChunk(
        chunk_sequence=sequence,
        simulation_session_id="session",
        reset_epoch=1,
        first_physics_step=physics_step,
        last_physics_step=physics_step,
        first_simulation_time_s=physics_step * 0.002,
        last_simulation_time_s=physics_step * 0.002,
        failed_publish_attempts=0,
        evidence_loss=False,
        samples=(sample,),
    )


class _BlockingStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.run_id = "session"
        self.started = Event()
        self.release = Event()

    def checkpoint_metadata(self, **_metadata) -> Path:
        return self.root / "run-index.json"

    def checkpoint_chunk(self, _chunk: PhysicsStepChunk) -> str:
        self.started.set()
        self.release.wait(timeout=2.0)
        return "digest"

    def checkpoint_boundary(self, _boundary) -> Path:
        return self.root / "run-index.json"

    def close_complete(self, **_terminal) -> Path:
        return self.root / "run-index.json"


def _observer(store) -> DynamicTransportEvidenceObserver:
    return DynamicTransportEvidenceObserver(
        simulation_session_id="session",
        reset_epoch=1,
        store=store,
        maximum_reaction_steps=25,
    )


def test_chunk_callback_returns_while_ordered_durable_write_is_blocked(tmp_path: Path) -> None:
    store = _BlockingStore(tmp_path)
    observer = _observer(store)
    returned = Event()
    errors: list[Exception] = []

    def accept() -> None:
        try:
            observer.accept_chunk(_chunk())
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)
        finally:
            returned.set()

    thread = Thread(target=accept)
    thread.start()
    assert store.started.wait(timeout=1.0)
    callback_returned_before_write = returned.wait(timeout=0.5)
    store.release.set()
    thread.join(timeout=1.0)

    assert callback_returned_before_write
    assert errors == []
    assert observer.latest_physics_step == 1
    observer.close_success(physical_transport_outcome="PROVED")


class _FailingStore(_BlockingStore):
    def checkpoint_chunk(self, _chunk: PhysicsStepChunk) -> str:
        raise OSError("disk failed")


def test_async_persistence_failure_invalidates_terminal_evidence(tmp_path: Path) -> None:
    observer = _observer(_FailingStore(tmp_path))

    observer.accept_chunk(_chunk())

    with pytest.raises(EvidenceInvalid, match="persistence.*disk failed"):
        observer.close_success(physical_transport_outcome="PROVED")


def test_terminal_close_drains_chunks_in_receive_order(tmp_path: Path) -> None:
    store = AtomicTransportEvidenceStore(tmp_path, run_id="session")
    observer = _observer(store)

    observer.accept_chunk(_chunk(sequence=7, physics_step=31))
    observer.accept_chunk(_chunk(sequence=8, physics_step=32))
    observer.mark_goal_dispatched(waypoint=1)
    observer.mark_waypoint_complete(waypoint=1)
    observer.mark_phase_complete(waypoint=1)
    index_path = observer.close_success(physical_transport_outcome="PROVED")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["status"] == "COMPLETE"
    assert [item["chunk_sequence"] for item in index["chunks"]] == [7, 8]
    assert [item["last_physics_step"] for item in index["chunks"]] == [31, 32]
    assert [item["kind"] for item in index["boundaries"]] == [
        "PHASE_START",
        "WAYPOINT_START",
        "WAYPOINT_END",
        "PHASE_END",
    ]
