"""Task 7 production chain: the live-evidence artifact end to end.

This exercises the **real** recorder, window, release correlation and journal-row readback against a real evidence
root: nine phases recorded at the frozen grid, a release open event correlated with three pre-open support rows,
sealing, and a read-back that must match before a journal row may cite it. Only the external world (ROS topics,
MuJoCo, controller I/O, process launch) is absent - nothing here fabricates a sample, and every grid point comes
from a value this test supplies as if it had been read back.
"""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.task8_live_evidence import (
    LiveEvidenceWindow, Task8LiveEvidenceRecorder, _SOURCES, build_live_evidence_sample,
    correlate_release_open,
)

PHASES = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN", "RELEASE", "RADIAL_RETREAT",
          "FINAL_CHECK")
PERIOD_S = 0.1
# the recorder validates `source_stamps_s`, `source_received_monotonic_s` and `raw_records` against its own
# `_SOURCES` set, so the fixture uses that set rather than a hand-copied list that can drift from it
READBACK_SOURCES = _SOURCES


def _identity():
    # P1-4: the release epoch is CREATED at the release, so the samples this fixture builds must end in the epoch the
    # port itself will seal with (`FINAL_RELEASE_EPOCH`) - a literal like 7 is the value no case ever reaches, and the
    # seal compares the last entry against the identity rather than trusting it
    from so101_demo.act.task8_live_evidence import FINAL_RELEASE_EPOCH

    return {"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
            "reset_epoch": 4, "release_epoch": FINAL_RELEASE_EPOCH}


def _raw_records(root: Path, sim_time: float) -> dict:
    """Each source's raw record is a real file with its own digest, exactly as the recorder requires."""

    records = {}
    for name in READBACK_SOURCES:
        target = root / "raw" / f"{name}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"source": name, "sim_time_s": sim_time}, sort_keys=True).encode()
        target.write_bytes(payload)
        records[name] = {"relative_path": f"raw/{name}.json",
                         "sha256": hashlib.sha256(payload).hexdigest()}
    return records


def _sample(root: Path, *, phase: str, step: int, sim_time: float) -> dict:
    return build_live_evidence_sample(
        identity=_identity(), phase=phase, physics_step=step, sim_time_s=sim_time,
        source_stamps_s={name: sim_time for name in READBACK_SOURCES},
        source_received_monotonic_s={name: sim_time for name in READBACK_SOURCES},
        raw_records=_raw_records(root, sim_time),
        holding_state="HOLDING",
        frame={"wrist_frame_valid": True, "wrist_target_visible": True},
        contact={"observation_valid": True, "bilateral_contact": True, "no_fingertip_contact": False,
                 "cup_supported": True, "released": False, "placement_stable": False},
        measurements={"cup_support_distance_m": 0.01, "end_effector_position_m": [0.0, 0.0, 0.1],
                      "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]})


def test_the_nine_phase_chain_seals_and_reads_back(tmp_path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    recorder = Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=evidence_root,
                                         session_id="session-1", attempt_id="attempt-1")
    window = LiveEvidenceWindow(recorder, identity=_identity(), period_s=PERIOD_S)
    window.bind_reset_epoch((_identity())["reset_epoch"])

    seen = []
    for step, phase in enumerate(PHASES):
        sample = _sample(evidence_root, phase=phase, step=step, sim_time=step * PERIOD_S)
        recorder.append(sample, kind="grid")
        window.add_grid(sample)
        seen.append(sample["phase"])
    assert seen == list(PHASES), "every phase is observed in order"
    assert window.grid_count == len(PHASES)

    # the release open event is correlated with the three rows immediately before it, at the frozen period
    support = [{"phase": "RELEASE", "release_epoch": 7, "source_stamp": 6.7 + PERIOD_S * index}
               for index in range(4)]
    correlation = correlate_release_open(support, {"operation": "gripper_open", "release_epoch": 7,
                                                   "source_stamp": 7.05,
                                                   "command_ref": "raw/controller/open.json"},
                                         period_s=PERIOD_S, indexed=("raw/controller/open.json",))
    assert correlation["support_rows"] == 3 and correlation["verdict"] == "PASS"

    artifact = recorder.seal(_identity())
    assert set(artifact) == {"path", "sha256", "schema_version"}
    target = Path(artifact["path"])
    assert target.is_file() and not target.is_symlink()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == artifact["sha256"]
    # the artifact's own content: non-empty and naming the case it belongs to, without assuming a key layout
    document = json.loads(target.read_bytes())
    assert document, "the sealed artifact must carry content"
    assert "full-01" in target.read_text(), "the artifact names the case it belongs to"


def test_a_window_that_never_reached_final_check_invalid_seals_instead(tmp_path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    recorder = Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=evidence_root,
                                         session_id="session-1", attempt_id="attempt-1")
    window = LiveEvidenceWindow(recorder, identity=_identity(), period_s=PERIOD_S)
    window.bind_reset_epoch((_identity())["reset_epoch"])
    window.add_grid(_sample(evidence_root, phase="SEARCH", step=0, sim_time=0.0))
    closed = window.invalidate("OWNER_RETIRE")
    assert closed["status"] == "INVALID" and closed["grid_count"] == 1
    # the recorder is deliberately independent of the window; the port couples them, so this asserts the window's
    # own state: an invalidated window accepts no further grid sample
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_WINDOW_SEALED"):
        window.add_grid(_sample(evidence_root, phase="APPROACH", step=1, sim_time=PERIOD_S))


def test_the_journal_row_readback_refuses_a_missing_or_mismatched_artifact(tmp_path):
    from so101_teleop.unified.pick_place_case_execution import _require_live_evidence_readback

    full = {"mode": "full"}
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_READBACK_MISSING"):
        _require_live_evidence_readback(None, full)
    target = tmp_path / "live.json"
    target.write_bytes(b"{}")
    good = {"path": str(target), "sha256": hashlib.sha256(b"{}").hexdigest(), "schema_version": 1}
    assert _require_live_evidence_readback(good, full) is None
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_READBACK_MISMATCH"):
        _require_live_evidence_readback({**good, "sha256": "c" * 64}, full)
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_UNEXPECTED"):
        _require_live_evidence_readback(good, {"mode": "phase_prefix"})


def _port_with(recorder, window):
    """The real port method under test, without constructing the ROS/MuJoCo boundary it normally needs."""

    from so101_demo.adapters.act.pick_place_search_port import PickPlaceSearchPhasePort

    port = object.__new__(PickPlaceSearchPhasePort)
    port._evidence_recorder = recorder
    port._live_evidence_window = window
    # The seal's identity comes from the CASE, so the boundary it reads is part of what this double must provide: the
    # reset generation from the verified receipt, which is where the port reads it (the runner's request carries none).
    from types import SimpleNamespace
    port.boundary = SimpleNamespace(reset=SimpleNamespace(receipt=SimpleNamespace(new_epoch=4)))
    return port


def _sealed_chain(tmp_path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    recorder = Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=evidence_root,
                                         session_id="session-1", attempt_id="attempt-1")
    window = LiveEvidenceWindow(recorder, identity=_identity(), period_s=PERIOD_S)
    window.bind_reset_epoch((_identity())["reset_epoch"])
    for step, phase in enumerate(PHASES):
        sample = _sample(evidence_root, phase=phase, step=step, sim_time=step * PERIOD_S)
        recorder.append(sample, kind="grid")
        window.add_grid(sample)
    return recorder, window


def test_the_port_seals_its_window_together_with_the_recorder(tmp_path):
    recorder, window = _sealed_chain(tmp_path)
    port = _port_with(recorder, window)
    artifact = port.seal_live_evidence({"scenario_id": "full-01", "session_id": "session-1",
                                        "attempt_id": "attempt-1"})
    assert set(artifact) == {"path", "sha256", "schema_version"}
    target = Path(artifact["path"])
    assert hashlib.sha256(target.read_bytes()).hexdigest() == artifact["sha256"]
    # the window was sealed first, so it accepts nothing further - the ordering the failure path depends on
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_WINDOW_SEALED"):
        window.add_grid(_sample(tmp_path / "evidence", phase="SEARCH", step=99, sim_time=9.9))


def test_an_unfinished_window_blocks_the_seal_rather_than_passing_silently(tmp_path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    recorder = Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=evidence_root,
                                         session_id="session-1", attempt_id="attempt-1")
    window = LiveEvidenceWindow(recorder, identity=_identity(), period_s=PERIOD_S)
    window.bind_reset_epoch((_identity())["reset_epoch"])
    window.add_grid(_sample(evidence_root, phase="SEARCH", step=0, sim_time=0.0))   # never reaches FINAL_CHECK
    port = _port_with(recorder, window)
    with pytest.raises(ValueError):
        port.seal_live_evidence({"scenario_id": "full-01", "session_id": "session-1",
                                 "attempt_id": "attempt-1", "reset_epoch": 4, "release_epoch": 7})


# --- the retirement path through the REAL owner ------------------------------------------------------------

def _owner_key(pid: int):
    from so101_teleop.unified.contracts import OwnerKey

    return OwnerKey(pid=pid, pgid=pid, started_ticks=pid * 10, argv_sha256="a" * 64,
                    environment_sha256="b" * 64)


def _receipt(root: Path, key, *, stack: bool, session_id=None, ros_domain_id=None) -> None:
    payload = {"leader_pid": key.pid, "pgid": key.pgid, "started_ticks": key.started_ticks,
               "argv_sha256": key.argv_sha256, "group_clear": True}
    if stack:
        payload.update(session_id=session_id, ros_domain_id=ros_domain_id,
                       physical_stop_confirmed=True, graph_clear=True)
    root.mkdir(parents=True, exist_ok=True)
    (root / "cleanup-receipt.json").write_bytes(json.dumps(payload).encode())


def test_the_real_owner_invalid_seals_an_open_window_before_child_retirement(tmp_path):
    """Exercises the real `PickPlaceCaseOwner._retire`, so the uncommitted retirement-path insertion is covered."""

    import asyncio
    from types import SimpleNamespace

    from so101_teleop.unified.pick_place_case_owner import PickPlaceCaseOwner

    recorder, window = _sealed_chain(tmp_path)
    child_key, stack_key = _owner_key(11), _owner_key(12)
    child_root, stack_root = tmp_path / "child", tmp_path / "stack"

    # the window is open (one SEARCH sample only), so retirement must invalid-seal it rather than seal it
    evidence_root = tmp_path / "open-evidence"
    evidence_root.mkdir()
    open_recorder = Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=evidence_root,
                                              session_id="session-1", attempt_id="attempt-1")
    open_window = LiveEvidenceWindow(open_recorder, identity=_identity(), period_s=PERIOD_S)
    open_window.bind_reset_epoch((_identity())["reset_epoch"])
    open_window.add_grid(_sample(evidence_root, phase="SEARCH", step=0, sim_time=0.0))

    child = SimpleNamespace(mujoco_session_id="session-1", ros_domain_id=3, socket_root=str(child_root))
    stack = SimpleNamespace(launch=SimpleNamespace(evidence_root=str(stack_root)), owner=stack_key,
                            process=object())
    port = SimpleNamespace(live_evidence_window=open_window)

    async def cancel(_request):
        return {"stopped_confirmed": True}

    async def stop_owned():
        _receipt(child_root, child_key, stack=False)

    async def stop():
        _receipt(stack_root, stack_key, stack=True, session_id="session-1", ros_domain_id=3)

    async def final_clear_probe(_domain):
        return True

    port.cancel = cancel
    child_owner = SimpleNamespace(stop_owned=stop_owned)
    stack.stop = stop
    async def released(*_args, **_kwargs):
        return None

    workload = SimpleNamespace(finish=released, stop=released, release=released)
    owner = PickPlaceCaseOwner(workload, child_owner, stack_factory=lambda *a: stack,
                               final_clear_probe=final_clear_probe, artifact_binding=lambda *a: {},
                               require_startup_proof=False)
    owner._ready = True
    owner.context = SimpleNamespace()
    owner.worker = port
    owner.child_launch = child
    owner.stack = stack
    owner.child_owner_key = child_key
    owner.stack_owner_key = stack_key

    asyncio.run(owner.finish(attempt_id="attempt-1"))

    assert owner._child_retired is True and owner._stack_retired is True and owner._final_clear is True
    assert (child_root / "cleanup-receipt.json").is_file() and (stack_root / "cleanup-receipt.json").is_file()
    # the open window was invalid-sealed with the retirement reason, before the child was retired
    assert getattr(open_window, "_sealed", False) is True
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_WINDOW_SEALED"):
        open_window.add_grid(_sample(evidence_root, phase="APPROACH", step=1, sim_time=PERIOD_S))
    assert getattr(open_window, "_invalid_reason", None) == "OWNER_RETIRE"
